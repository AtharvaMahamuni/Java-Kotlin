
public class MaxSellProblem {

    public static int maxSellProblemMethod(int[] array) {
        int maxProfit = 0;
        int minValue = array[0];

        for (int value : array) {
            if (value < minValue) {
                minValue = value;
            }

            if (maxProfit < (value - minValue)) {
                maxProfit = value - minValue;
            }
        }

        return maxProfit;
    }

    public static void main(String[] args) {
        int[] array1 = { 9, 12, 5, 6, 7, 10, 8 };

        System.out.println(maxSellProblemMethod(array1));
    }
}
